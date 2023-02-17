#include<iostream>
using namespace std;
int main()
{
	//declearation
	int Roll_number,paper1,paper2,paper3,paper4,paper5,TotalMarks;
	string FirstName,lastName;
	//User input
	cout<<"Roll Number : ";
	cin>>Roll_number;
	cout<<"First Name : ";
	cin>>FirstName;
	cout<<"last Name : ";
	cin>>lastName;
	cout<<endl<<FirstName.append(lastName)<<endl;
	cout<<" Marks in Islamiat : ";
	cin>>paper1;
	cout<<" Marks in OOP : ";
	cin>>paper2;
	cout<<" Marks in DLD : ";
	cin>>paper3;
	cout<<" Marks in DE : ";
	cin>>paper4;
	cout<<" Marks in Presentation Skills : ";
	cin>>paper5;
	if(paper1>100 || paper2>100 || paper3>100 || paper4>100 || paper5>100 || paper1<0 || paper2<0 || paper3<0 || paper4<0 || paper5<0)
	{
		cout<<"INVALID DATA"<<endl;
	}
	else
	{
		TotalMarks= paper1+paper2+paper3+paper4+paper5;
		cout<<"Total Marks : "<<TotalMarks<<" out of 500"<<endl;
	}
	int Parcentage = (TotalMarks * 100) / 500;
	cout<<"Parcentage : "<<Parcentage<<endl;
	if(Parcentage >=80  && Parcentage <=100)
	{
		cout<<"Grade A";
	}
	else if(Parcentage>=70 && Parcentage <80 )
	{
		cout<<"Grade B";
	}
	else if(Parcentage>=60 && Parcentage <70 )
	{
		cout<<"Grade C";
	}
	else if(Parcentage>=50 && Parcentage <60 )
	{
		cout<<"Grade D";
	}
	else if(Parcentage <40)
	{
		cout<<"Fail";
	}
}
